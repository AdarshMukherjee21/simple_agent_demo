import streamlit as st
import logging
import json
import os
from langchain_core.messages import HumanMessage
from agent import agent_executor

# --- 1. SETUP LOGGER & HISTORY ---
logging.basicConfig(
    filename='agent_history.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("EmailAgent")

HISTORY_FILE = "chat_history.json"

def load_history():
    """Loads chat and log history from a local JSON file."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading history: {e}")
    return {"messages": [], "step_logs": []}

def save_history():
    """Saves chat and log history to a local JSON file."""
    with open(HISTORY_FILE, "w") as f:
        json.dump({
            "messages": st.session_state.messages,
            "step_logs": st.session_state.step_logs
        }, f, indent=4)

# --- 2. SETUP UI CONFIG ---
st.set_page_config(page_title="AI Email Agent", layout="wide")
st.title(" Autonomous Email Agent")

# --- 3. INITIALIZE SESSION STATE ---
history = load_history()
if "messages" not in st.session_state:
    st.session_state.messages = history.get("messages", [])
if "thread_id" not in st.session_state:
    st.session_state.thread_id = "session_1"
if "step_logs" not in st.session_state:
    st.session_state.step_logs = history.get("step_logs", [])
if "current_query" not in st.session_state:
    st.session_state.current_query = None

config = {"configurable": {"thread_id": st.session_state.thread_id}}

# --- 4. HELPER FUNCTION TO RUN AGENT & TRACK PROGRESS ---
def run_agent_and_track(inputs):
    """Streams LangGraph updates and logs/stores them for the right pane."""
    try:
        for event in agent_executor.stream(inputs, config, stream_mode="updates"):
            for node_name, state_update in event.items():
                step_msg = f" Executed Node: `{node_name}`"
                
                if "messages" in state_update:
                    last_msg = state_update["messages"][-1]
                    if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
                        tools = [tc['name'] for tc in last_msg.tool_calls]
                        step_msg += f"\n\n **Tools Requested**: {', '.join(tools)}"
                
                if st.session_state.step_logs:
                    st.session_state.step_logs[-1]["steps"].append(step_msg)
                
                logger.info(f"Thread {st.session_state.thread_id} | Node: {node_name} | Update: {state_update}")
        
        # Save progress after every run
        save_history()
    except Exception as e:
        st.error(f"Agent Execution Failed: {str(e)}")

# --- 5. CREATE LEFT & RIGHT PANES ---
chat_col, log_col = st.columns([2, 1], gap="large")

# ================================
# RIGHT PANE: PROGRESS & LOGS
# ================================
with log_col:
    st.subheader(" Agent Progress")
    st.caption("Expand a query to see the agent's internal routing.")
    
    for log_entry in reversed(st.session_state.step_logs):
        short_query = log_entry['query'][:40] + "..." if len(log_entry['query']) > 40 else log_entry['query']
        with st.expander(f"Query: {short_query}", expanded=True):
            if not log_entry['steps']:
                st.write(" Processing...")
            for i, step in enumerate(log_entry['steps']):
                st.markdown(f"**Step {i+1}**\n{step}")
                st.divider()

# ================================
# LEFT PANE: CHAT INTERFACE
# ================================
with chat_col:
    # Wrap messages in a fixed-height container to force the chat input to stay at the bottom
    chat_container = st.container(height=650)
    
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # Check LangGraph state to see if execution paused before the "tools" node
    state = agent_executor.get_state(config)
    is_interrupted = len(state.next) > 0 and state.next[0] == "tools"

    if is_interrupted:
        last_message = state.values["messages"][-1]
        
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                
                # Handle Email Tool (Requires Human Confirmation)
                if tool_call["name"] == "send_email":
                    st.warning(" The agent is requesting permission to send an email.")
                    args = tool_call["args"]
                    st.code(f"To: {args.get('recipient_email')}\nSubject: {args.get('subject')}\n\n{args.get('body')}")
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Approve & Send"):
                            if st.session_state.step_logs:
                                st.session_state.step_logs[-1]["steps"].append("👤 *User Approved Email Execution*")
                            
                            with st.spinner("Executing tool..."):
                                run_agent_and_track(None)
                                final_state = agent_executor.get_state(config)
                                final_response = final_state.values["messages"][-1].content
                                st.session_state.messages.append({"role": "assistant", "content": final_response})
                                save_history()
                                st.rerun()
                    with c2:
                        if st.button("❌ Deny & Modify"):
                            denial_msg = "I denied sending this email draft. Please revise or ask me what to change."
                            st.session_state.messages.append({"role": "user", "content": denial_msg})
                            if st.session_state.step_logs:
                                st.session_state.step_logs[-1]["steps"].append("👤 *User Denied Email Execution*")
                            save_history()
                            st.rerun()
                
                # Handle Fetch Contact (Auto-Executes, but now safely captures the draft)
                elif tool_call["name"] == "fetch_contact":
                    with st.spinner("Looking up contact..."):
                        run_agent_and_track(None)
                        
                        # Grab the newly generated draft text after resuming
                        new_state = agent_executor.get_state(config)
                        
                        # If the agent didn't immediately call another tool, print its text output
                        if len(new_state.next) == 0 or new_state.next[0] != "tools":
                            final_msg = new_state.values["messages"][-1].content
                            st.session_state.messages.append({"role": "assistant", "content": final_msg})
                            save_history()
                    st.rerun()

    else:
        if prompt := st.chat_input("E.g., Send an email to Kunal reminding him about tomorrow..."):
            
            st.session_state.current_query = prompt
            st.session_state.step_logs.append({"query": prompt, "steps": []})
            st.session_state.messages.append({"role": "user", "content": prompt})
            save_history()
            
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(prompt)
                
                with st.chat_message("assistant"):
                    with st.spinner("Reasoning..."):
                        run_agent_and_track({"messages": [HumanMessage(content=prompt)]})
                        
                        new_state = agent_executor.get_state(config)
                        if len(new_state.next) > 0 and new_state.next[0] == "tools":
                            st.rerun()
                        else:
                            response_text = new_state.values["messages"][-1].content
                            st.markdown(response_text)
                            st.session_state.messages.append({"role": "assistant", "content": response_text})
                            save_history()
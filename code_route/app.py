# Minimal comment added for commit
import base64
import json  # Import json for parsing tool results

import streamlit as st

from .config import Config
from .assistant import Assistant


def init_state():
    if "assistant" not in st.session_state:
        st.session_state.assistant = Assistant()
        st.session_state.messages = []  # Store full message dictionaries
        st.session_state.image_data = None
        # st.session_state.last_tool = None # No longer needed

def add_message(message: dict): # Accept the full message dict
    st.session_state.messages.append(message)

def render_chat():
    for message in st.session_state.messages:
        role = message["role"]
        content = message["content"]

        with st.chat_message("user" if role == "user" else "assistant"):
            # --- User Messages ---
            if role == "user":
                if isinstance(content, list):  # image + text sequence
                    for block in content:
                        if block.get("type") == "image":
                            st.image(base64.b64decode(block["source"]["data"]))
                        elif block.get("type") == "text":
                            st.markdown(block["text"])
                else:
                    st.markdown(content) # Simple text message

            # --- Assistant Messages ---
            elif role == "assistant":
                # Display text content if available
                if content:
                     st.markdown(content)

                # Display tool calls if present
                if message.get("tool_calls"):
                    st.markdown("---") # Separator
                    calls = message["tool_calls"]
                    if len(calls) == 1:
                         st.markdown(f"🔧 Using tool: **{calls[0].function.name}**")
                    else:
                         tool_names = ", ".join([f"**{call.function.name}**" for call in calls])
                         st.markdown(f"🔧 Using tools: {tool_names}")
                    # Optional: Display arguments if desired
                    # for call in calls:
                    #     try:
                    #         args = json.loads(call.function.arguments)
                    #         st.json(args)
                    #     except json.JSONDecodeError:
                    #         st.text(f"Args: {call.function.arguments}") # Fallback

            # --- Tool Messages ---
            elif role == "tool":
                st.markdown(f"--- Tool Result: **{message.get('name', 'Unknown Tool')}** ---")
                try:
                    # Attempt to parse content as JSON
                    tool_result = json.loads(content)
                    # Check if the result is a dictionary or list (likely JSON data)
                    if isinstance(tool_result, (dict, list)):
                        st.json(tool_result)
                    # Check if it's a string that looks like code
                    elif isinstance(tool_result, str) and ('def ' in tool_result or 'import ' in tool_result or '{' in tool_result or '=>' in tool_result or 'const ' in tool_result):
                         st.code(tool_result, language='python') # Or detect language?
                    else:
                        st.markdown(tool_result) # Render as markdown otherwise
                except json.JSONDecodeError:
                    # If not JSON, treat as plain text/code
                    if isinstance(content, str) and ('def ' in content or 'import ' in content or '{' in content or '=>' in content or 'const ' in content):
                         st.code(content, language='python') # Basic code detection
                    else:
                         st.markdown(content) # Render as markdown

def main():
    st.set_page_config(page_title="Code Route", page_icon="📡", layout="wide")
    init_state()

    # Header -------------------------------------------------------------
    col1, col2, col3, col4 = st.columns([1, 4, 1, 1])
    with col2:
        st.markdown("## 🛤️  **Code Route**  – your coding copilot")
    with col3:
        # Model selection
        current_model = st.session_state.assistant.current_model
        selected_model = st.selectbox(
            "Model", 
            options=list(Config.AVAILABLE_MODELS.keys()),
            format_func=lambda x: Config.AVAILABLE_MODELS[x],
            index=list(Config.AVAILABLE_MODELS.keys()).index(current_model),
            key="model_selector"
        )
        if selected_model != current_model:
            message = st.session_state.assistant.set_model(selected_model)
            if message.startswith("Error"):
                st.warning(message)
            elif message.startswith("Already"):
                st.info(message)
            else:
                st.session_state.messages.append({"role": "system", "content": message})
                st.rerun()
    with col4:
        if st.button("🔄 Reset", use_container_width=True):
            st.session_state.assistant.reset()
            st.session_state.messages = []
            st.rerun()

    st.divider()

    # Chat history -------------------------------------------------------
    render_chat()

    # Token usage bar ----------------------------------------------------
    total_tokens = getattr(st.session_state.assistant, "total_tokens_used", 0)
    pct = total_tokens / Config.MAX_CONVERSATION_TOKENS
    st.progress(pct, text=f"{total_tokens:,} / {Config.MAX_CONVERSATION_TOKENS:,} tokens")

    # Image upload -------------------------------------------------------
    uploaded_img = st.file_uploader("Attach image", type=["png", "jpg", "jpeg", "gif", "webp"],
                                   key="uploader", label_visibility="collapsed")
    if uploaded_img is not None:
        img_bytes = uploaded_img.read()
        st.image(img_bytes, caption="Preview", width=200)
        st.session_state.image_data = base64.b64encode(img_bytes).decode()
    else:
        st.session_state.image_data = None

    # Chat input ---------------------------------------------------------
    prompt = st.chat_input("Type something… (⌘/Ctrl + Enter to send)")
    if prompt is not None or st.session_state.image_data:
        # Prepare message content structure for user input
        user_content = prompt
        if st.session_state.image_data:
            user_content_list = [{
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg", # Assume jpeg for now
                        "data": st.session_state.image_data
                    }
                }]
            if prompt:
                user_content_list.append({"type": "text", "text": prompt})
            user_content = user_content_list # Use the list structure

        # Add user message
        user_message_struct = {"role": "user", "content": user_content}
        add_message(user_message_struct)

        # Render chat immediately after adding user message
        # This requires finding the container where chat is rendered if not the main page
        # For simplicity, we'll rely on the full rerun after assistant response for now.
        # Consider using st.container() for the chat history if immediate update is needed.
        # render_chat() # Re-rendering here might be complex with Streamlit's flow

        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                # Store length before assistant call
                messages_before_call = len(st.session_state.assistant.conversation_history)

                try:
                    # Call the assistant (it modifies its own history)
                    # The actual response text is less important now, we'll pull from history
                    _ = st.session_state.assistant.chat(user_content)
                except Exception as e:
                    # Add error message directly to Streamlit state if assistant fails
                    error_message = {"role": "assistant", "content": f"**Error:** {e}"}
                    add_message(error_message)
                    st.markdown(error_message["content"]) # Display error immediately

                # Add new messages from assistant history to Streamlit state
                new_messages = st.session_state.assistant.conversation_history[messages_before_call:]
                for msg in new_messages:
                    add_message(msg)

                # Clear the image data after processing
                st.session_state.image_data = None
                # Force a rerun to render the new messages added via add_message
                st.rerun()

    # Footer -------------------------------------------------------------
    st.caption("© 2025 Code Route – Powered by Streamlit")

if __name__ == "__main__":
    main()
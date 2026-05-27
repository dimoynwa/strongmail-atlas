from google.genai import types
from google.adk.runners import Runner
from google.adk.events import Event
from google.adk.sessions import BaseSessionService, Session


# ANSI color codes for terminal output
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"

    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Background colors
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"


async def display_state(
    session_service: BaseSessionService, app_name: str, user_id: str, session_id: str, label="Current State"
):
    """Display the current session state in a formatted way."""
    try:
        session: Session = await session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )

        # Format the output with clear sections
        print(f"\n{'-' * 10} {label} {'-' * 10}")

        # Handle the user name
        user_name = session.state.get("user_name", "Unknown")
        print(f"👤 User: {user_name}")

        # Handle othrer state properties
        for k, v in session.state.items():
            if k != 'user_name' and k != 'eligible_keys' and k != 'tone_bearing_keys':
                print(f"📝 {k}: {v}")
            elif k == 'eligible_keys':
                print(f"📝 eligible_keys: {len(v)} keys")
            elif k == 'tone_bearing_keys':
                print(f"📝 tone_bearing_keys: {len(v)} keys")
        print("-" * (22 + len(label)))
    except Exception as e:
        print(f"Error displaying state: {e}")

async def process_agent_response(event: Event, verbose: bool):
    """Process and display agent response events."""
    # Log basic event info
    if verbose:
        print(f"Event ID: {event.id}, Author: {event.author}")

    # Check for specific parts first
    # has_specific_part = False
    if verbose and event.content and event.content.parts:
        for part in event.content.parts:
            if hasattr(part, "executable_code") and part.executable_code:
                # Access the actual code string via .code
                print(
                    f"  Debug: Agent generated code:\n```python\n{part.executable_code.code}\n```"
                )
                # has_specific_part = True
            elif hasattr(part, "code_execution_result") and part.code_execution_result:
                # Access outcome and output correctly
                print(
                    f"  Debug: Code Execution Result: {part.code_execution_result.outcome} - Output:\n{part.code_execution_result.output}"
                )
                # has_specific_part = True
            elif hasattr(part, "tool_response") and part.tool_response:
                # Print tool response information
                print(f"  Tool Response: {part.tool_response.output}")
                # has_specific_part = True
            # Also print any text parts found in any event for debugging
            elif hasattr(part, "text") and part.text and not part.text.isspace():
                print(f"  Text: '{part.text.strip()}'")

    # Check for final response after specific parts
    final_response = None
    
    # Heuristic: If we see a text part that looks like our JSON output, capture it as potential final response
    if event.content and event.content.parts:
        for part in event.content.parts:
            if hasattr(part, "text") and part.text:
                txt = part.text.strip()
                if '"processed":' in txt and ('"cards":' in txt or '"reason":' in txt):
                    final_response = txt

    if event.is_final_response() and not final_response:
        if (
            event.content
            and event.content.parts
            and hasattr(event.content.parts[0], "text")
            and event.content.parts[0].text
        ):
            final_response = event.content.parts[0].text.strip()
            # Use colors and formatting to make the final response stand out
            print(
                f"\n{Colors.BG_BLUE}{Colors.WHITE}{Colors.BOLD}╔══ AGENT RESPONSE {event.author} ═════════════════════════════════════════{Colors.RESET}"
            )
            print(f"{Colors.CYAN}{Colors.BOLD}{final_response}{Colors.RESET}")
            print(
                f"{Colors.BG_BLUE}{Colors.WHITE}{Colors.BOLD}╚═════════════════════════════════════════════════════════════{Colors.RESET}\n"
            )
        else:
            print(
                f"\n{Colors.BG_RED}{Colors.WHITE}{Colors.BOLD}==> Final Agent Response: [No text content in final event]{Colors.RESET}\n"
            )

    return final_response


async def call_agent_async(runner: Runner, user_id: str, session_id: str, query: str,
                           verbose: bool = True):
    """Call the agent asynchronously with the user's query."""
    content = types.Content(role="user", parts=[types.Part(text=query)])
    if verbose:
        print(
            f"\n{Colors.BG_GREEN}{Colors.BLACK}{Colors.BOLD}--- Running Query: {query} ---{Colors.RESET}"
        )
    runner.session_service
    final_response_text = None

    # Display state before processing
    if verbose:
        await display_state(
            runner.session_service,
            runner.app_name,
            user_id,
            session_id,
            "State BEFORE processing",
        )

    try:
        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=content
        ):
            # Process each event and get the final response if available
            response = await process_agent_response(event, verbose)
            if response:
                final_response_text = response
    except Exception as e:
        print(f"Error during agent call: {e}")
        final_response_text = f'{{"processed": true, "cards": [], "reason": "Internal Error: {str(e)}"}}'

    # Display state after processing the message
    if verbose:
        await display_state(
            runner.session_service,
            runner.app_name,
            user_id,
            session_id,
            "State AFTER processing",
        )

    # Cleanup markdown code blocks if present
    if final_response_text:
        cleaned = final_response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
            
        final_response_text = cleaned.strip()

    return final_response_text

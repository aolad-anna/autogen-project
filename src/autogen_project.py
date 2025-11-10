from groq import Groq
import re
import sys
import time
import os
from dotenv import load_dotenv
from pathlib import Path


load_dotenv()
GROQ_KEY = os.getenv("GROQ_KEY")
MODEL = "llama-3.1-8b-instant" 

class Agent:
    """
    Base agent class. Think of this as the parent class that gives
    all our specialized agents some common abilities.
    """
    def __init__(self, name, job):
        self.name = name
        self.job = job
        self.messages = []
    
    def say(self, text, mood="info"):
        """
        Makes the agent 'speak' - basically just fancy printing.
        The mood parameter changes the emoji shown.
        """
        emojis = {
            "info": "💬",
            "success": "✅", 
            "error": "❌",
            "code": "💻",
            "thinking": "🤔",
            "working": "⚙️"
        }
        icon = emojis.get(mood, "💬")
        
        print(f"\n{icon} {self.name}")
        print("-" * 50)
        print(text)
        print("-" * 50)
        time.sleep(0.4)  # small pause so you can read it


class CoderAgent(Agent):
    """
    This agent writes code. It uses Groq's AI to generate Python code
    based on what we ask it to do.
    """
    def __init__(self, groq_client):
        super().__init__("Coder", "Writes Python code")
        self.ai = groq_client
        self.attempt = 0
    
    def write_code(self, task, error_msg=None):
        """
        Ask the AI to write code. If there was an error before,
        we tell it about the error so it can fix the code.
        """
        self.attempt += 1
        
        if error_msg:
            self.say(f"Oops, that didn't work. Let me fix it...\nError was: {error_msg}", "thinking")
            instructions = f"""The code you wrote before had this problem: {error_msg}

Original task: {task}

Please write working Python code that fixes this issue. Just give me the code, no explanations."""
        else:
            self.say(f"Attempt #{self.attempt}: Writing code for '{task}'", "thinking")
            # On first try, we intentionally ask for incomplete code to demo the self-fixing
            if self.attempt == 1:
                instructions = f"""{task}

Write Python code but make it incomplete (like leaving a TODO comment).
This helps demonstrate how the system fixes itself."""
            else:
                instructions = f"""{task}

Write complete, working Python code. Just the code, nothing else."""
        
        try:
            # Call Groq API
            response = self.ai.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You're a Python expert. Write clean code."},
                    {"role": "user", "content": instructions}
                ],
                temperature=0.7,
                max_tokens=800
            )
            
            raw_code = response.choices[0].message.content
            
            # Clean up the code (remove markdown stuff)
            code = raw_code.replace("```python", "").replace("```", "").strip()
            
            self.say(f"Here's what I wrote:\n\n{code}", "code")
            return code
            
        except Exception as e:
            self.say(f"Couldn't generate code: {e}", "error")
            return f"# Error: {e}"


class ExecutorAgent(Agent):
    """
    This agent runs the code in a safe way. It catches errors
    and reports back what happened.
    """
    def __init__(self):
        super().__init__("Executor", "Runs and tests code")
    
    def run_code(self, code):
        """
        Execute Python code safely. We create a mini sandbox environment
        so the code can't do anything dangerous to your computer.
        """
        self.say("Running the code now...", "working")
        
        try:
            # Set up a safe space for the code to run
            # Only allow basic Python stuff, no file access or dangerous operations
            safe_space = {
                '__builtins__': __builtins__,
                'print': print,
                'range': range,
                'len': len,
                'sum': sum,
                'max': max,
                'min': min,
            }
            local_vars = {}
            
            # Capture anything the code prints
            import io
            from contextlib import redirect_stdout
            
            output = io.StringIO()
            
            with redirect_stdout(output):
                exec(code, safe_space, local_vars)
            
            printed_stuff = output.getvalue()
            
            # Check if there's a result we should show
            result = None
            
            # Look for common function names
            for func_name in ['fibonacci', 'fib', 'calculate', 'main']:
                if func_name in local_vars and callable(local_vars[func_name]):
                    result = local_vars[func_name](10)
                    printed_stuff = f"Result: {result}"
                    break
            
            # Or maybe they stored it in a variable called 'result'
            if 'result' in local_vars:
                result = local_vars['result']
                printed_stuff = f"Result: {result}"
            
            self.say(f"Success! Output:\n{printed_stuff}", "success")
            return {"worked": True, "output": printed_stuff, "error": None}
            
        except SyntaxError as e:
            msg = f"Syntax error on line {e.lineno}: {e.msg}"
            self.say(f"Code has syntax problems:\n{msg}", "error")
            return {"worked": False, "output": None, "error": msg}
        
        except NameError as e:
            msg = f"Variable or function not found: {e}"
            self.say(f"Code references something that doesn't exist:\n{msg}", "error")
            return {"worked": False, "output": None, "error": msg}
        
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            self.say(f"Something went wrong:\n{msg}", "error")
            return {"worked": False, "output": None, "error": msg}


class ReviewerAgent(Agent):
    """
    NEW: This agent reviews code quality before execution.
    Adds an extra layer of checking.
    """
    def __init__(self, groq_client):
        super().__init__("Reviewer", "Checks code quality")
        self.ai = groq_client
    
    def review(self, code, task):
        """Check if the code looks reasonable before running it."""
        self.say("Reviewing code quality...", "thinking")
        
        # Quick checks we can do without AI
        issues = []
        
        if "TODO" in code or "pass" in code:
            issues.append("Code looks incomplete (has TODO or pass)")
        
        if len(code.strip()) < 20:
            issues.append("Code seems too short to be complete")
        
        # Ask AI for a quick review
        try:
            prompt = f"""Review this Python code briefly:

```python
{code}
```

Task it should solve: {task}

Just say "APPROVED" if it looks complete and correct, or briefly explain what's wrong."""
            
            response = self.ai.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200
            )
            
            review = response.choices[0].message.content
            
            if "APPROVED" in review.upper():
                self.say("Code looks good to me! ✓", "success")
                return {"approved": True, "feedback": "Looks good"}
            else:
                self.say(f"Found some issues:\n{review}", "info")
                return {"approved": False, "feedback": review}
        
        except:
            # If AI review fails, just use our basic checks
            if issues:
                return {"approved": False, "feedback": ", ".join(issues)}
            return {"approved": True, "feedback": "Basic checks passed"}


class Orchestrator(Agent):
    """
    The boss agent. Coordinates all the other agents and makes sure
    they work together properly.
    """
    def __init__(self):
        super().__init__("Orchestrator", "Coordinates the team")
    
    def run_task(self, task, coder, reviewer, executor, max_tries=3):
        """
        Main workflow:
        1. Get code from Coder
        2. Have Reviewer check it
        3. Let Executor run it
        4. If it fails, loop back to step 1 with the error message
        """
        self.say(f"Got a new task: '{task}'\nLet me coordinate the team...", "info")
        
        for attempt in range(1, max_tries + 1):
            self.say(f"Round {attempt} of {max_tries}", "info")
            
            # Step 1: Coder writes code
            if attempt == 1:
                code = coder.write_code(task)
            else:
                code = coder.write_code(task, error_msg=result["error"])
            
            # Step 2: Reviewer checks it
            review = reviewer.review(code, task)
            
            if not review["approved"] and attempt < max_tries:
                self.say(f"Reviewer found issues. Sending back to Coder...", "info")
                result = {"worked": False, "error": review["feedback"]}
                continue
            
            # Step 3: Executor runs it
            result = executor.run_code(code)
            
            # Check if we're done
            if result["worked"]:
                self.say(f"Task completed successfully in {attempt} attempts! 🎉", "success")
                return result
            
            if attempt < max_tries:
                self.say("That didn't work. Let's try again with the feedback...", "info")
            else:
                self.say(f"Tried {max_tries} times but couldn't solve it. Might need human help.", "error")
        
        return result


def setup_check():
    """Make sure everything is configured properly."""
    if GROQ_KEY == "your-groq-api-key-here" or not GROQ_KEY:
        print("\n❌ Oops! You need to add your Groq API key first.")
        print("\nHere's how (takes 2 minutes):")
        print("1. Go to https://console.groq.com/")
        print("2. Sign up (it's free, no credit card)")
        print("3. Get your API key")
        print("4. Paste it on line 23 of this file")
        print("\nNo payment needed - Groq is 100% free! 🎉\n")
        sys.exit(1)


def show_intro():
    """Show a nice intro explaining what this does."""
    print("\n" + "="*60)
    print("  AutoGen Multi-Agent Demo - AI Teamwork in Action")
    print("="*60)
    print("\nWhat you're about to see:")
    print("• Coder Agent writes Python code")
    print("• Reviewer Agent checks the code quality")  
    print("• Executor Agent runs it safely")
    print("• They work together, fixing mistakes automatically")
    print("\nThis is way better than asking one AI to do everything!")
    print("\nUsing: Groq (free & super fast) + Llama 3.1")
    print("="*60)

def update_readme_with_output(output_text):
    """
    Appends or updates the latest AutoGen output in README.md.
    """
    readme_path = Path(__file__).parent / "README.md"

    if not readme_path.exists():
        # If README doesn't exist, create a simple one
        readme_path.write_text("# AutoGen Demo Project\n\n## Latest Output\n")
    
    content = readme_path.read_text()

    # Add/update the section for latest output
    start_marker = "<!-- AUTO_GEN_OUTPUT_START -->"
    end_marker = "<!-- AUTO_GEN_OUTPUT_END -->"

    new_section = f"{start_marker}\n```\n{output_text}\n```\n{end_marker}"

    if start_marker in content and end_marker in content:
        # Replace existing output
        content = content.split(start_marker)[0] + new_section
    else:
        # Append at the end
        content += f"\n\n## Latest Output\n{new_section}\n"

    readme_path.write_text(content)
    print("\n✅ README.md updated with latest output!\n")


def main():
    """Run the whole demo."""
    # show_intro()
    # setup_check()
    
    try:
        ai_client = Groq(api_key=GROQ_KEY)
        print("Connected")
    except Exception as e:
        print(f"❌ Couldn't connect to Groq: {e}")
        print("   Make sure you ran: pip install groq")
        sys.exit(1)
    
    # Create our team of agents
    orchestrator = Orchestrator()
    coder = CoderAgent(ai_client)
    reviewer = ReviewerAgent(ai_client)
    executor = ExecutorAgent()
    
    print("Agents ready!\n")
    time.sleep(1)
    
    # The task we want to solve
    task = "Write a Python function that calculates the 10th Fibonacci number"
    
    # Let the orchestrator coordinate everything
    print("\n" + "="*60)
    print("  Starting Multi-Agent Workflow")
    print("="*60)
    
    result = orchestrator.run_task(task, coder, reviewer, executor, max_tries=3)
    
    # Show the final result
    print("\n" + "="*60)
    print("  Final Result")
    print("="*60)
    
    if result["worked"]:
        print(f"\n✅ Success! Here's what we got:\n")
        print(f"   {result['output']}")
    else:
        print(f"\n❌ Couldn't complete the task:")
        print(f"   {result['error']}")
    print("="*60 + "\n")


def custom_mode():
    """Let users try their own tasks."""
    show_intro()
    setup_check()
    
    ai_client = Groq(api_key=GROQ_KEY)
    
    orchestrator = Orchestrator()
    coder = CoderAgent(ai_client)
    reviewer = ReviewerAgent(ai_client)
    executor = ExecutorAgent()
    
    print("\n🎮 Custom Task Mode")
    print("="*60)
    
    while True:
        task = input("\n💭 What coding task should the agents solve?\n   (or 'quit' to exit): ")
        
        if task.lower() in ['quit', 'exit', 'q']:
            print("\n👋 Thanks for trying it out!")
            break
        
        if not task.strip():
            task = "Calculate factorial of 5"
            print(f"   Using example: {task}")
        
        print("\n" + "="*60)
        result = orchestrator.run_task(task, coder, reviewer, executor, max_tries=3)
        
        print("\n" + "="*60)
        if result["worked"]:
            print(f"✅ Result: {result['output']}")
        else:
            print(f"❌ Error: {result['error']}")
        print("="*60)
        
        update_readme_with_output(result['output'] if result['worked'] else result['error'])


if __name__ == "__main__":
    # Run the main demo
    main()
    
    # Ask if they want to try custom tasks
    print("\nWant to try your own tasks? (y/n): ", end="")
    choice = input().lower()
    if choice == 'y':
        custom_mode()
import openai
import os
import argparse
import yaml
import sys
import logging
from blessings import Terminal
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings

openai.api_key = os.getenv("OPENAI_API_KEY")

SYSTEM_PROMPT_DEV = f"You are a helpful assistant who is an expert in software development. You are helping a user who is a software developer. Your responses are short and concise. You include code snippets when appropriate. Code snippets are formatted using Markdown. User's `uname`: {os.uname()}"

INIT_USER_PROMPT_DEV = "Your responses must be short and concise. Do not include explanations unless asked."

SYSTEM_PROMPT_GENERAL = "You are a helpful assistant."


def init_messages(assistant_type):
    if assistant_type == "dev":
        return [
            {"role": "system", "content": SYSTEM_PROMPT_DEV},
            {"role": "user", "content": INIT_USER_PROMPT_DEV},
        ]
    elif assistant_type == "general":
        return [{"role": "system", "content": SYSTEM_PROMPT_GENERAL}]


TERMINAL_WELCOME = """
Hi! I'm here to help. Type `q` or Ctrl-D to exit, `c` or Ctrl-C to clear
the conversation, `r` or Ctrl-R to re-generate the last response. 
To enter multi-line mode, enter a backslash `\` followed by a new line.
Exit the multi-line mode by pressing ESC and then Enter (Meta+Enter).
"""

COMMAND_CLEAR = ("clear", "c")
COMMAND_QUIT = ("quit", "q")
COMMAND_RERUN = ("rerun", "r")


def complete_chat(messages, model):
    response_iter = openai.ChatCompletion.create(
        model=model, messages=messages, temperature=0.7, stream=True
    )

    # Now iterate over the response iterator to yield the next response
    for response in response_iter:
        next_choice = response["choices"][0]
        if next_choice["finish_reason"] is None and "content" in next_choice["delta"]:
            yield next_choice["delta"]["content"]


class ChatSession:
    def __init__(self, assistant_type, model):
        self.assistant_type = assistant_type
        self.model = model
        self.messages = init_messages(assistant_type)
        self.term = Terminal()
        self.prompt_session = PromptSession()

    def clear(self):
        self.messages = init_messages(self.assistant_type)
        print(self.term.bold("Cleared the conversation."))

    def rerun(self):
        if len(self.messages) == len(init_messages(self.assistant_type)):
            print(self.term.bold("Nothing to re-run."))
            return

        self.messages = self.messages[:-1]
        print(self.term.bold("Re-generating the last message."))
        logging.info("Re-generating the last message.")
        self.respond()

    def respond(self):
        next_response = []
        try:
            for response in complete_chat(self.messages, self.model):
                next_response.append(response)
                print(self.term.green(response), end="", flush=True)
        except KeyboardInterrupt:
            # If the user interrupts the chat completion, we'll just return what we have so far
            pass

        print("\n")
        next_response = {"role": "assistant", "content": "".join(next_response)}
        logging.info(next_response)
        self.messages.append(next_response)

    def prompt(self, multiline=False):
        bindings = KeyBindings()

        @bindings.add("c-c")
        def _ctrl_c(event):
            if len(event.current_buffer.text) == 0 and not multiline:
                event.current_buffer.text = COMMAND_CLEAR[0]
                event.current_buffer.validate_and_handle()
            else:
                event.app.exit(exception=KeyboardInterrupt, style="class:aborting")

        @bindings.add("c-d")
        def _ctrl_d(event):
            if len(event.current_buffer.text) == 0:
                if not multiline:
                    event.current_buffer.text = COMMAND_QUIT[0]
                event.current_buffer.validate_and_handle()

        @bindings.add("c-r")
        def _ctrl_r(event):
            if len(event.current_buffer.text) == 0:
                event.current_buffer.text = COMMAND_RERUN[0]
                event.current_buffer.validate_and_handle()

        try:
            return self.prompt_session.prompt(
                "> " if not multiline else "multiline> ",
                vi_mode=True,
                multiline=multiline,
                enable_open_in_editor=True,
                key_bindings=bindings,
            )
        except KeyboardInterrupt:
            return ""

    def request_input(self):
        line = self.prompt()

        if line != "\\":
            return line

        return self.prompt(multiline=True)

    def loop(self):
        print(self.term.bold(TERMINAL_WELCOME))

        while True:
            while (next_user_input := self.request_input()) == "":
                pass

            if next_user_input in COMMAND_QUIT:
                break

            if next_user_input in COMMAND_CLEAR:
                self.clear()
                logging.info("Cleared the conversation.")
                continue

            if next_user_input in COMMAND_RERUN:
                self.rerun()
                continue

            user_message = {"role": "user", "content": next_user_input}
            self.messages.append(user_message)
            logging.info(user_message)
            self.respond()


def read_yaml_config(file_path):
    with open(file_path, "r") as file:
        return yaml.safe_load(file)


default_exception_handler = sys.excepthook


def exception_handler(type, value, traceback):
    logging.exception("Uncaught exception", exc_info=(type, value, traceback))
    print("An uncaught exception occurred. Please report this issue on GitHub.")
    default_exception_handler(type, value, traceback)


sys.excepthook = exception_handler


def main():
    config_path = os.path.expanduser("~/.gptrc")
    config = read_yaml_config(config_path) if os.path.isfile(config_path) else {}

    parser = argparse.ArgumentParser(description="Run a chat session with ChatGPT.")
    parser.add_argument(
        "assistant",
        type=str,
        default=config.get("assistant", "dev"),
        nargs="?",
        choices=["dev", "general"],
        help="The type of assistant to use. `dev` (default) is a software development assistant, `general` is a generally helpful assistant.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=config.get("model", "gpt-3.5-turbo"),
        help="The model to use for the chat session.",
    )
    parser.add_argument(
        "--log_file",
        type=str,
        default=config.get("log_file", None),
        help="The file to log the chat session to.",
    )
    parser.add_argument(
        "--log_level",
        type=str,
        default=config.get("log_level", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="The log level to use.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        filename=args.log_file,
        level=args.log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logging.info("Starting a new chat session. Config = %s", args)

    session = ChatSession(assistant_type=args.assistant, model=args.model)
    session.loop()


if __name__ == "__main__":
    main()

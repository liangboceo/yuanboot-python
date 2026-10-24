from yuanboot import Configuration


class GreetingService:
    def __init__(self, configuration: Configuration):
        self.configuration = configuration

    def greet(self, name: str) -> str:
        return f"{self.configuration.get_string('greeting.message')}, {name}!"

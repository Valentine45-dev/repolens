from scoring.services import default_difficulty


class Challenge:
    def save(self):
        return default_difficulty()

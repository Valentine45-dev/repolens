import logging

from sample_app.models import User

log = logging.getLogger(__name__)


def create_user(name: str, email: str) -> User:
    user = User(name=name, email=email)
    user.save()
    return user


async def fetch_user(user_id: int):
    def _key(uid):
        return f"user:{uid}"

    log.info("fetching %s", _key(user_id))
    return None


if __name__ == "__main__":
    def main():
        create_user("a", "a@example.com")

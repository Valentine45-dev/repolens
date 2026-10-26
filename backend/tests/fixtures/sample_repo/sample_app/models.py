from dataclasses import dataclass


class Base:
    def save(self):
        raise NotImplementedError


@dataclass
class User(Base):
    name: str
    email: str

    @property
    def display_name(self) -> str:
        return self.name.title()

    def save(self):
        return {"name": self.name, "email": self.email}

    class Meta:
        table = "users"

        def describe(cls):
            return cls.table

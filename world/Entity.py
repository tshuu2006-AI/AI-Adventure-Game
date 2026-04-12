class BaseEntity():
    def __init__(self, id, name, type, description):
        self.id = id
        self.name = name
        self.type = type
        self.description = description


class Item(BaseEntity):
    def __init__(self, id, name, description):
        super().__init__(id, name, "item", description)


class Location(BaseEntity):
    def __init__(self, id, name, description):
        super().__init__(id, name, "location", description)


class NPC(BaseEntity):
    def __init__(self, id, name, personality, description, affectionlevel, location):
        super().__init__(id, name, 'npc', description)
        self.personality = personality
        self.affectionlevel = affectionlevel
        self.location = location


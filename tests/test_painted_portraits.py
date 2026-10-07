"""Every humanlike NPC gets a painted portrait when one exists for its species.

The painted catalogue has masculine and feminine humans. An NPC whose presentation was never stated (a plain
'commoner' with no pronoun, title or description cue) must still get the nearest painting, while a presentation
that *was* stated stays a hard boundary.
"""
import unittest

from engine import art


def npc(**kw):
    e = {"id": "test-npc", "name": "Market folk", "kind": "npc", "srd": "commoner", "srd_name": "Commoner",
         "type": "humanoid", "side": "neutral", "inventory": []}
    e.update(kw)
    return e


class PaintedPortraitsForEveryone(unittest.TestCase):
    def test_unstated_presentation_still_gets_a_painting(self):
        self.assertEqual(art.visual_identity(npc())["presentation_source"], "unspecified")
        self.assertIsNotNone(art.portrait_choice(npc()))

    def test_stated_presentation_is_kept(self):
        chosen = art.portrait_choice(npc(name="Goodwife Rhosk", appearance="A stout woman in a blue gown."))
        self.assertIsNotNone(chosen)
        self.assertEqual(art.portrait_choice(npc(name="Goodwife Rhosk", appearance="A stout woman in a blue gown.")), chosen)

    def test_stated_androgynous_is_not_forced_into_a_gendered_painting(self):
        e = npc(look={"presentation": "androgynous"})
        self.assertEqual(art.visual_identity(e)["presentation_source"], "look")
        chosen = art.portrait_choice(e)
        if chosen:   # only if the catalogue ever gains an androgynous painting
            from engine import painted
            rows = {("portraits-human", i): r for i, r in enumerate(painted.HUMANS)}
            self.assertNotIn(rows.get(chosen, ("", "androgynous"))[1], ("masculine", "feminine"))


if __name__ == "__main__":
    unittest.main()

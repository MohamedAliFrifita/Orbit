"""
Analyst — recupere/parse la liste d'exposants d'un evenement selectionne.

SEMAINE 1 : donnees mockees, aucun scraping reel.
SEMAINE 2 : brancher `tools.fetch_exhibitor_list` + `tools.enrich_company`.
"""

from orbit.schemas.exhibitor import ExhibitorInput
from orbit.schemas.run import SelectedEvent


async def run(event: SelectedEvent) -> list[ExhibitorInput]:
    # TODO(semaine 2): remplacer par un vrai scraping/parsing du catalogue d'exposants
    return [
        ExhibitorInput(
            id="ex_001",
            name="Example Corp",
            booth="Hall 4 - B22",
            raw_description="Fabricant de systemes d'automatisation industrielle, 200+ employes.",
        ),
        ExhibitorInput(
            id="ex_002",
            name="Concurrent SA",
            booth="Hall 2 - A10",
            raw_description="Editeur de logiciels de supervision industrielle.",
        ),
        ExhibitorInput(
            id="ex_003",
            name="Composants Plus",
            booth="Hall 4 - C05",
            raw_description="Distributeur de composants electroniques pour l'industrie.",
        ),
    ]

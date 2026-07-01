"""High-level adapter implementing the domain's SharpOddsProvider port on top
of The Odds API.

Scoped to one `sport_key` per instance (i.e. one competition): every Odds API
request needs a sport_key and the domain has nowhere to carry one, so the
composition root is expected to build one instance per league being tracked.
"""

from src.domain.entities.match import Match
from src.domain.entities.odds_quote import OddsQuote
from src.domain.ports.sharp_odds_provider import SharpOddsProvider
from src.infrastructure.providers.api.client import TheOddsApiClient
from src.infrastructure.providers.api.mappers import odds_quotes_from_event_odds_dto


class TheOddsApiSharpOddsProvider(SharpOddsProvider):
    def __init__(
        self,
        client: TheOddsApiClient,
        sport_key: str,
        *,
        sharp_bookmaker_key: str = "pinnacle",
        region: str = "eu",
    ) -> None:
        self._client = client
        self._sport_key = sport_key
        self._sharp_bookmaker_key = sharp_bookmaker_key
        self._region = region

    async def get_odds(self, match: Match) -> list[OddsQuote]:
        dto = await self._client.get_event_odds(
            self._sport_key,
            match.id,
            regions=self._region,
            markets="h2h",
            bookmakers=self._sharp_bookmaker_key,
        )
        return odds_quotes_from_event_odds_dto(
            dto, sharp_bookmaker_key=self._sharp_bookmaker_key, region=self._region
        )

    async def get_sharp_1x2_odds_for_matches(
        self, matches: list[Match]
    ) -> dict[str, list[OddsQuote]]:
        """Batch variant beyond the SharpOddsProvider port: one API call
        covers every event in this sport, then only the requested matches
        are kept - much cheaper than calling `get_odds` once per match when
        a use case already has a whole slate to price. Matches not found in
        the response are simply absent from the result, not an error."""
        dtos = await self._client.list_odds(
            self._sport_key,
            regions=self._region,
            markets="h2h",
            bookmakers=self._sharp_bookmaker_key,
        )
        wanted_ids = {match.id for match in matches}
        return {
            dto.id: odds_quotes_from_event_odds_dto(
                dto, sharp_bookmaker_key=self._sharp_bookmaker_key, region=self._region
            )
            for dto in dtos
            if dto.id in wanted_ids
        }

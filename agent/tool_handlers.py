"""
Routes tool_use blocks from Claude to the appropriate LinkedInClient methods.
All handlers return a JSON string (the tool_result content).
Errors are returned as JSON so Claude can reason about them rather than crashing.
"""

import json
from typing import Any

from linkedin.client import LinkedInClient
from linkedin.exceptions import LinkedInAPIError


class ToolHandler:
    def __init__(self, client: LinkedInClient, account_id: str):
        self._client = client
        self._account_id = account_id  # default account for the session
        self._registry = {
            "list_ad_accounts": self._list_ad_accounts,
            "list_campaign_groups": self._list_campaign_groups,
            "create_campaign_group": self._create_campaign_group,
            "list_campaigns": self._list_campaigns,
            "create_campaign": self._create_campaign,
            "update_campaign": self._update_campaign,
            "search_targeting_facets": self._search_targeting_facets,
            "list_saved_audiences": self._list_saved_audiences,
            "list_conversions": self._list_conversions,
            "associate_conversions": self._associate_conversions,
            "create_direct_sponsored_content": self._create_direct_sponsored_content,
            "create_ad": self._create_ad,
        }

    def dispatch(self, tool_name: str, tool_input: dict) -> str:
        """
        Dispatch a tool call and return a JSON string result.
        Errors from LinkedIn are returned as JSON so Claude can handle them gracefully.
        """
        handler = self._registry.get(tool_name)
        if not handler:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        try:
            result = handler(tool_input)
            return json.dumps(result, default=str)
        except LinkedInAPIError as e:
            return json.dumps(
                {
                    "error": e.message,
                    "status_code": e.status_code,
                    "error_code": e.error_code,
                    "hint": _error_hint(e.status_code),
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _account(self, inp: dict) -> str:
        return inp.get("account_id") or self._account_id

    # ------------------------------------------------------------------
    # Handler implementations
    # ------------------------------------------------------------------

    def _list_ad_accounts(self, _: dict) -> list:
        return self._client.list_ad_accounts()

    def _list_campaign_groups(self, inp: dict) -> list:
        return self._client.list_campaign_groups(self._account(inp))

    def _create_campaign_group(self, inp: dict) -> dict:
        return self._client.create_campaign_group(
            account_id=self._account(inp),
            name=inp["name"],
            total_budget_amount=inp["total_budget_amount"],
            total_budget_currency=inp["total_budget_currency"],
            start_date=inp.get("start_date"),
            end_date=inp.get("end_date"),
        )

    def _list_campaigns(self, inp: dict) -> list:
        return self._client.list_campaigns(self._account(inp))

    def _create_campaign(self, inp: dict) -> dict:
        return self._client.create_campaign(
            account_id=self._account(inp),
            campaign_group_id=inp["campaign_group_id"],
            name=inp["name"],
            objective=inp["objective"],
            campaign_type=inp.get("campaign_type", "SPONSORED_UPDATES"),
            bid_strategy=inp.get("bid_strategy", "LOWEST_COST"),
            daily_budget_amount=inp.get("daily_budget_amount"),
            daily_budget_currency=inp.get("daily_budget_currency"),
            total_budget_amount=inp.get("total_budget_amount"),
            total_budget_currency=inp.get("total_budget_currency"),
            unit_cost_amount=inp.get("unit_cost_amount"),
            unit_cost_currency=inp.get("unit_cost_currency"),
            targeting_criteria=inp.get("targeting_criteria"),
            start_date=inp.get("start_date"),
            end_date=inp.get("end_date"),
            locale=inp.get("locale", "en_US"),
        )

    def _update_campaign(self, inp: dict) -> dict:
        campaign_id = inp.pop("campaign_id")
        return self._client.update_campaign(campaign_id, **inp)

    def _search_targeting_facets(self, inp: dict) -> list:
        return self._client.search_targeting_facets(
            facet_type=inp["facet_type"],
            query=inp["query"],
        )

    def _list_saved_audiences(self, inp: dict) -> list:
        return self._client.list_saved_audiences(self._account(inp))

    def _list_conversions(self, inp: dict) -> list:
        return self._client.list_conversions(self._account(inp))

    def _associate_conversions(self, inp: dict) -> dict:
        return self._client.associate_conversions(
            campaign_id=inp["campaign_id"],
            conversion_ids=inp["conversion_ids"],
        )

    def _create_direct_sponsored_content(self, inp: dict) -> dict:
        return self._client.create_direct_sponsored_content(
            account_id=self._account(inp),
            name=inp["name"],
            introductory_text=inp["introductory_text"],
            destination_url=inp["destination_url"],
            call_to_action=inp["call_to_action"],
            headline=inp.get("headline", ""),
            description=inp.get("description", ""),
            image_media_asset_urn=inp.get("image_media_asset_urn"),
        )

    def _create_ad(self, inp: dict) -> dict:
        return self._client.create_ad(
            campaign_id=inp["campaign_id"],
            creative_reference=inp["creative_reference"],
        )


def _error_hint(status_code: int) -> str:
    hints = {
        401: "Token expired or invalid. Run 'python main.py login' to re-authenticate.",
        403: "Permission denied. Ensure your LinkedIn app has the rw_ads scope and Marketing Developer Platform access.",
        400: "Invalid request. Check that all field values are correct.",
        429: "Rate limit hit. Wait a moment before retrying.",
        500: "LinkedIn API server error. Try again in a few seconds.",
    }
    return hints.get(status_code, "Check the LinkedIn Marketing API documentation.")

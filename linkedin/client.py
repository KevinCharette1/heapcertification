"""
LinkedIn Marketing API client.

All public methods return plain dicts so results can be trivially
serialised to JSON strings for Claude tool_result blocks.

API reference:
  v2 endpoints:  https://api.linkedin.com/v2/
  Campaign Manager API: https://learn.microsoft.com/en-us/linkedin/marketing/
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from linkedin.exceptions import LinkedInAPIError, TokenExpiredError
from linkedin.models import FACET_URN_MAP

TOKENS_FILE = Path("tokens.json")


class LinkedInClient:
    BASE_URL = "https://api.linkedin.com/v2"

    def __init__(self, tokens: dict, settings):
        self._tokens = tokens
        self._settings = settings
        self._http = httpx.Client(timeout=30.0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        self._maybe_refresh()
        return {
            "Authorization": f"Bearer {self._tokens['access_token']}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def _maybe_refresh(self):
        expiry_str = self._tokens.get("expiry")
        if not expiry_str:
            return
        expiry = datetime.fromisoformat(expiry_str)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry - datetime.now(timezone.utc) < timedelta(minutes=5):
            self._do_refresh()

    def _do_refresh(self):
        from linkedin.oauth import refresh_tokens
        try:
            updated = refresh_tokens(self._tokens, self._settings)
            self._tokens.update(updated)
            with open(TOKENS_FILE, "w") as f:
                json.dump(self._tokens, f, indent=2)
        except TokenExpiredError:
            raise TokenExpiredError(
                "Your LinkedIn session has expired. Run 'python main.py login' to re-authenticate."
            )

    def _request(
        self,
        method: str,
        path: str,
        extra_headers: dict | None = None,
        **kwargs,
    ) -> dict:
        url = f"{self.BASE_URL}/{path.lstrip('/')}"
        headers = self._headers()
        if extra_headers:
            headers.update(extra_headers)

        response = self._http.request(method, url, headers=headers, **kwargs)

        if response.status_code == 204:
            return {}

        if not response.is_success:
            try:
                err = response.json()
                message = err.get("message") or err.get("errorDetails") or response.text
                service_code = int(err.get("serviceErrorCode", 0))
            except Exception:
                message = response.text
                service_code = 0
            raise LinkedInAPIError(
                status_code=response.status_code,
                message=message,
                error_code=service_code,
            )

        return response.json()

    @staticmethod
    def _to_epoch_ms(date_str: str) -> int:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)

    @staticmethod
    def _urn_id(urn: str) -> str:
        """Extract the numeric ID from a URN like urn:li:sponsoredCampaign:123."""
        return urn.split(":")[-1]

    # ------------------------------------------------------------------
    # Ad Accounts
    # ------------------------------------------------------------------

    def list_ad_accounts(self) -> list[dict]:
        """List all LinkedIn ad accounts accessible to the authenticated user."""
        data = self._request(
            "GET",
            "adAccountsV2",
            params={
                "q": "search",
                "search.type.values[0]": "BUSINESS",
                "search.status.values[0]": "ACTIVE",
                "count": 100,
            },
        )
        results = []
        for el in data.get("elements", []):
            results.append(
                {
                    "id": f"urn:li:sponsoredAccount:{el['id']}",
                    "name": el.get("name", "Unknown"),
                    "status": el.get("status", ""),
                    "currency": el.get("currency", "USD"),
                    "type": el.get("type", ""),
                }
            )
        return results

    # ------------------------------------------------------------------
    # Campaign Groups
    # ------------------------------------------------------------------

    def list_campaign_groups(self, account_id: str) -> list[dict]:
        data = self._request(
            "GET",
            "adCampaignGroupsV2",
            params={
                "q": "search",
                "search.account.values[0]": account_id,
                "count": 100,
            },
        )
        return [
            {
                "id": f"urn:li:sponsoredCampaignGroup:{el['id']}",
                "name": el.get("name", ""),
                "status": el.get("status", ""),
            }
            for el in data.get("elements", [])
        ]

    def create_campaign_group(
        self,
        account_id: str,
        name: str,
        status: str = "PAUSED",
        total_budget_amount: str | None = None,
        total_budget_currency: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "account": account_id,
            "name": name,
            "status": status,
        }

        if total_budget_amount and total_budget_currency:
            payload["totalBudget"] = {
                "amount": total_budget_amount,
                "currencyCode": total_budget_currency,
            }

        run_schedule: dict[str, int] = {
            "start": self._to_epoch_ms(start_date)
            if start_date
            else int(datetime.now(timezone.utc).timestamp() * 1000)
        }
        if end_date:
            run_schedule["end"] = self._to_epoch_ms(end_date)
        payload["runSchedule"] = run_schedule

        response = self._request("POST", "adCampaignGroupsV2", json=payload)
        group_id = response.get("id", "unknown")
        return {
            "id": f"urn:li:sponsoredCampaignGroup:{group_id}",
            "name": name,
            "status": status,
        }

    # ------------------------------------------------------------------
    # Campaigns
    # ------------------------------------------------------------------

    def list_campaigns(self, account_id: str) -> list[dict]:
        data = self._request(
            "GET",
            "adCampaignsV2",
            params={
                "q": "search",
                "search.account.values[0]": account_id,
                "count": 100,
            },
        )
        return [
            {
                "id": f"urn:li:sponsoredCampaign:{el['id']}",
                "name": el.get("name", ""),
                "status": el.get("status", ""),
                "objective": el.get("objectiveType", ""),
                "type": el.get("type", ""),
            }
            for el in data.get("elements", [])
        ]

    def create_campaign(
        self,
        account_id: str,
        campaign_group_id: str,
        name: str,
        objective: str,
        campaign_type: str = "SPONSORED_UPDATES",
        bid_strategy: str = "LOWEST_COST",
        daily_budget_amount: str | None = None,
        daily_budget_currency: str | None = None,
        total_budget_amount: str | None = None,
        total_budget_currency: str | None = None,
        unit_cost_amount: str | None = None,
        unit_cost_currency: str | None = None,
        targeting_criteria: dict | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        locale: str = "en_US",
    ) -> dict:
        # Derive costType from bid strategy
        cost_type = "CPC" if bid_strategy in ("TARGET_COST", "MANUAL") else "CPM"

        locale_parts = locale.replace("-", "_").split("_")
        locale_obj = {
            "country": locale_parts[1].upper() if len(locale_parts) > 1 else "US",
            "language": locale_parts[0].lower(),
        }

        payload: dict[str, Any] = {
            "account": account_id,
            "campaignGroup": campaign_group_id,
            "name": name,
            "status": "PAUSED",
            "type": campaign_type,
            "objectiveType": objective,
            "costType": cost_type,
            "locale": locale_obj,
        }

        if daily_budget_amount and daily_budget_currency:
            payload["dailyBudget"] = {
                "amount": daily_budget_amount,
                "currencyCode": daily_budget_currency,
            }
        if total_budget_amount and total_budget_currency:
            payload["totalBudget"] = {
                "amount": total_budget_amount,
                "currencyCode": total_budget_currency,
            }
        if unit_cost_amount and unit_cost_currency:
            payload["unitCost"] = {
                "amount": unit_cost_amount,
                "currencyCode": unit_cost_currency,
            }
        if targeting_criteria:
            payload["targetingCriteria"] = targeting_criteria

        run_schedule: dict[str, int] = {
            "start": self._to_epoch_ms(start_date)
            if start_date
            else int(datetime.now(timezone.utc).timestamp() * 1000)
        }
        if end_date:
            run_schedule["end"] = self._to_epoch_ms(end_date)
        payload["runSchedule"] = run_schedule

        response = self._request("POST", "adCampaignsV2", json=payload)
        campaign_id = response.get("id", "unknown")
        return {
            "id": f"urn:li:sponsoredCampaign:{campaign_id}",
            "name": name,
            "status": "PAUSED",
            "account_id": account_id,
            "campaign_group_id": campaign_group_id,
            "objective": objective,
        }

    def update_campaign(self, campaign_id: str, **fields) -> dict:
        """Partial update a campaign (status, budget, end date)."""
        numeric_id = self._urn_id(campaign_id)
        patch: dict[str, Any] = {}

        if "status" in fields:
            patch["status"] = fields["status"]
        if fields.get("daily_budget_amount") and fields.get("daily_budget_currency"):
            patch["dailyBudget"] = {
                "amount": fields["daily_budget_amount"],
                "currencyCode": fields["daily_budget_currency"],
            }
        if fields.get("end_date"):
            patch.setdefault("runSchedule", {})["end"] = self._to_epoch_ms(
                fields["end_date"]
            )

        self._request(
            "POST",
            f"adCampaignsV2/{numeric_id}",
            extra_headers={"X-RestLi-Method": "PARTIAL_UPDATE"},
            json={"patch": {"$set": patch}},
        )
        return {"id": campaign_id, "updated_fields": list(patch.keys())}

    # ------------------------------------------------------------------
    # Targeting
    # ------------------------------------------------------------------

    def search_targeting_facets(self, facet_type: str, query: str) -> list[dict]:
        """
        Search LinkedIn's targeting taxonomy for URNs.
        facet_type: one of TITLES, INDUSTRIES, GEO, COMPANIES, SENIORITIES, SKILLS,
                    JOB_FUNCTIONS, COMPANY_SIZE
        """
        facet_urn = FACET_URN_MAP.get(facet_type.upper())
        if not facet_urn:
            return [
                {
                    "error": f"Unknown facet type '{facet_type}'. Valid types: {list(FACET_URN_MAP)}"
                }
            ]

        data = self._request(
            "GET",
            "adTargetingEntities",
            params={
                "q": "typeahead",
                "query": query,
                "facetUrn": facet_urn,
                "count": 10,
            },
        )
        return [
            {"urn": el.get("urn", ""), "name": el.get("name", "")}
            for el in data.get("elements", [])
        ]

    # ------------------------------------------------------------------
    # Saved / Matched Audiences
    # ------------------------------------------------------------------

    def list_saved_audiences(self, account_id: str) -> list[dict]:
        """
        List matched audiences (retargeting, contact lists, lookalikes) for an account.
        Requires Marketing Developer Platform access on the LinkedIn app.
        """
        try:
            data = self._request(
                "GET",
                "adAudiencesV3",
                params={
                    "q": "owner",
                    "owner": account_id,
                    "count": 100,
                },
            )
            return [
                {
                    "id": f"urn:li:adAudience:{el.get('id', '')}",
                    "name": el.get("name", ""),
                    "type": el.get("type", ""),
                    "size": el.get("size", 0),
                    "status": el.get("status", ""),
                }
                for el in data.get("elements", [])
            ]
        except LinkedInAPIError as e:
            return [
                {
                    "warning": "Could not fetch saved audiences",
                    "reason": e.message,
                    "hint": "Ensure your app has Marketing Developer Platform access and rw_ads scope.",
                }
            ]

    # ------------------------------------------------------------------
    # Conversions
    # ------------------------------------------------------------------

    def list_conversions(self, account_id: str) -> list[dict]:
        """List conversion tracking actions configured for an ad account."""
        try:
            data = self._request(
                "GET",
                "adConversionsV2",
                params={
                    "q": "search",
                    "search.account.values[0]": account_id,
                    "count": 100,
                },
            )
            return [
                {
                    "id": f"urn:li:adConversion:{el.get('id', '')}",
                    "name": el.get("name", ""),
                    "type": el.get("type", ""),
                    "post_click_window_days": el.get("postClickAttributionWindowSize", 30),
                    "enabled": el.get("enabled", True),
                }
                for el in data.get("elements", [])
            ]
        except LinkedInAPIError as e:
            return [
                {
                    "warning": "Could not fetch conversions",
                    "reason": e.message,
                    "hint": "Ensure conversions are set up in Campaign Manager under Account Assets → Conversions.",
                }
            ]

    def associate_conversions(
        self, campaign_id: str, conversion_ids: list[str]
    ) -> dict:
        """Associate one or more conversion actions with a campaign."""
        results = []
        for cid in conversion_ids:
            try:
                self._request(
                    "POST",
                    "adCampaignConversionsV2",
                    json={"campaign": campaign_id, "conversion": cid},
                )
                results.append({"conversion_id": cid, "success": True})
            except LinkedInAPIError as e:
                results.append(
                    {"conversion_id": cid, "success": False, "error": e.message}
                )
        return {"campaign_id": campaign_id, "results": results}

    # ------------------------------------------------------------------
    # Ad Creatives
    # ------------------------------------------------------------------

    def create_direct_sponsored_content(
        self,
        account_id: str,
        name: str,
        introductory_text: str,
        destination_url: str,
        call_to_action: str,
        headline: str = "",
        description: str = "",
        image_media_asset_urn: str | None = None,
    ) -> dict:
        """
        Create a Direct Sponsored Content (dark post) ad.
        Returns the DSC URN to be used in create_ad.
        """
        thumbnails = (
            [{"resolvedUrl": image_media_asset_urn}] if image_media_asset_urn else []
        )

        payload = {
            "owner": account_id,
            "name": name,
            "type": "SPONSORED_STATUS_UPDATE",
            "subject": introductory_text,
            "content": {
                "contentEntities": [
                    {
                        "entityLocation": destination_url,
                        "thumbnails": thumbnails,
                    }
                ],
                "title": headline or name,
                "description": description,
                "landingPageUrl": destination_url,
                "callToAction": {"label": call_to_action},
            },
        }
        response = self._request("POST", "adDirectSponsoredContents", json=payload)
        dsc_id = response.get("id", "unknown")
        return {
            "id": f"urn:li:adDirectSponsoredContent:{dsc_id}",
            "name": name,
            "status": "DRAFT",
            "destination_url": destination_url,
            "call_to_action": call_to_action,
        }

    def create_ad(
        self,
        campaign_id: str,
        creative_reference: str,
        status: str = "PAUSED",
    ) -> dict:
        """
        Create an ad by associating a creative with a campaign.
        creative_reference: urn:li:adDirectSponsoredContent:XXX
                            or urn:li:ugcPost:XXX (existing organic post)
        Status defaults to PAUSED — activate manually in Campaign Manager.
        """
        payload = {
            "campaign": campaign_id,
            "status": status,
            "type": "SPONSORED_UPDATE_V2",
            "variables": {
                "data": {
                    "com.linkedin.ads.SponsoredUpdateCreativeVariables": {
                        "directSponsoredContent": {
                            "reference": creative_reference,
                        }
                    }
                }
            },
        }
        response = self._request("POST", "adCreativesV2", json=payload)
        creative_id = response.get("id", "unknown")
        return {
            "id": f"urn:li:sponsoredCreative:{creative_id}",
            "campaign_id": campaign_id,
            "creative_reference": creative_reference,
            "status": status,
        }

    def close(self):
        self._http.close()

"""
Anthropic tool definitions for the LinkedIn Campaign Agent.
Each tool maps 1-to-1 to a LinkedInClient method.
"""

LINKEDIN_TOOLS = [
    {
        "name": "list_ad_accounts",
        "description": (
            "List all LinkedIn ad accounts accessible to the authenticated user. "
            "Call this at the start of every session if the account ID is unknown."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_campaign_groups",
        "description": "List existing campaign groups for the active ad account.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {
                    "type": "string",
                    "description": "LinkedIn ad account URN, e.g. 'urn:li:sponsoredAccount:123'. "
                    "Defaults to the active account if omitted.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "create_campaign_group",
        "description": (
            "Create a LinkedIn campaign group (container for related campaigns). "
            "Always created as PAUSED. Returns the new campaign group URN."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "name": {"type": "string"},
                "total_budget_amount": {
                    "type": "string",
                    "description": "Optional group-level total budget as decimal string, e.g. '5000.00'",
                },
                "total_budget_currency": {
                    "type": "string",
                    "description": "ISO 4217 currency code, e.g. 'USD'",
                },
                "start_date": {
                    "type": "string",
                    "description": "ISO 8601 date YYYY-MM-DD. Defaults to today.",
                },
                "end_date": {
                    "type": "string",
                    "description": "ISO 8601 date YYYY-MM-DD. Leave blank for ongoing.",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "list_campaigns",
        "description": "List all campaigns in the active ad account.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"}
            },
            "required": [],
        },
    },
    {
        "name": "create_campaign",
        "description": (
            "Create a LinkedIn campaign inside a campaign group. "
            "Always created as PAUSED — nothing spends until activated. "
            "Call search_targeting_facets first to resolve URNs for all targeting terms."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "campaign_group_id": {
                    "type": "string",
                    "description": "URN of the parent campaign group.",
                },
                "name": {"type": "string"},
                "objective": {
                    "type": "string",
                    "enum": [
                        "BRAND_AWARENESS",
                        "WEBSITE_VISITS",
                        "ENGAGEMENT",
                        "VIDEO_VIEWS",
                        "LEAD_GENERATION",
                        "WEBSITE_CONVERSIONS",
                        "JOB_APPLICANTS",
                    ],
                },
                "campaign_type": {
                    "type": "string",
                    "enum": [
                        "SPONSORED_UPDATES",
                        "TEXT_AD",
                        "SPONSORED_INMAILS",
                        "DYNAMIC",
                    ],
                    "description": "Ad format. SPONSORED_UPDATES = Single Image/Carousel/Video in feed.",
                },
                "bid_strategy": {
                    "type": "string",
                    "enum": ["LOWEST_COST", "TARGET_COST", "MANUAL"],
                    "description": "LOWEST_COST is recommended — LinkedIn auto-optimises.",
                },
                "daily_budget_amount": {
                    "type": "string",
                    "description": "Daily spend cap as decimal string, e.g. '75.00'",
                },
                "daily_budget_currency": {"type": "string", "description": "e.g. 'USD'"},
                "total_budget_amount": {"type": "string"},
                "total_budget_currency": {"type": "string"},
                "unit_cost_amount": {
                    "type": "string",
                    "description": "Target CPC/CPM bid for TARGET_COST or MANUAL strategies.",
                },
                "unit_cost_currency": {"type": "string"},
                "targeting_criteria": {
                    "type": "object",
                    "description": (
                        "LinkedIn targeting object with 'include' and optional 'exclude' keys. "
                        "Each key contains an 'and' array of 'or' objects mapping facet URNs to "
                        "arrays of targeting entity URNs. "
                        "Example: {\"include\": {\"and\": [{\"or\": {\"urn:li:adTargetingFacet:locations\": [\"urn:li:geo:103644278\"]}}]}}"
                    ),
                },
                "start_date": {
                    "type": "string",
                    "description": "YYYY-MM-DD. Defaults to today.",
                },
                "end_date": {
                    "type": "string",
                    "description": "YYYY-MM-DD. Omit for ongoing campaigns.",
                },
                "locale": {
                    "type": "string",
                    "description": "Language_Country code, e.g. 'en_US'. Default: 'en_US'.",
                },
            },
            "required": ["campaign_group_id", "name", "objective", "campaign_type"],
        },
    },
    {
        "name": "update_campaign",
        "description": "Update an existing campaign's status, daily budget, or end date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": "Campaign URN, e.g. 'urn:li:sponsoredCampaign:123'",
                },
                "status": {
                    "type": "string",
                    "enum": ["ACTIVE", "PAUSED", "ARCHIVED"],
                },
                "daily_budget_amount": {"type": "string"},
                "daily_budget_currency": {"type": "string"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["campaign_id"],
        },
    },
    {
        "name": "search_targeting_facets",
        "description": (
            "Search LinkedIn's targeting taxonomy to find URNs for job titles, industries, "
            "locations, companies, seniority levels, skills, job functions, or company sizes. "
            "Always call this before building a targeting_criteria object — never guess URNs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "facet_type": {
                    "type": "string",
                    "enum": [
                        "TITLES",
                        "INDUSTRIES",
                        "GEO",
                        "COMPANIES",
                        "SENIORITIES",
                        "SKILLS",
                        "JOB_FUNCTIONS",
                        "COMPANY_SIZE",
                    ],
                    "description": "The type of targeting entity to search.",
                },
                "query": {
                    "type": "string",
                    "description": "Search term, e.g. 'Software Engineer' or 'San Francisco'",
                },
            },
            "required": ["facet_type", "query"],
        },
    },
    {
        "name": "list_saved_audiences",
        "description": (
            "List matched/saved audiences in the active ad account — retargeting lists, "
            "contact list uploads, lookalike audiences, and engagement audiences. "
            "Offer these to the user before building custom attribute targeting."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"}
            },
            "required": [],
        },
    },
    {
        "name": "list_conversions",
        "description": (
            "List conversion tracking actions configured in the active ad account. "
            "Present these when the campaign objective is WEBSITE_CONVERSIONS or LEAD_GENERATION."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"}
            },
            "required": [],
        },
    },
    {
        "name": "associate_conversions",
        "description": "Associate one or more conversion actions with a campaign for tracking.",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": "Campaign URN to attach conversions to.",
                },
                "conversion_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of conversion URNs, e.g. ['urn:li:adConversion:123']",
                },
            },
            "required": ["campaign_id", "conversion_ids"],
        },
    },
    {
        "name": "create_direct_sponsored_content",
        "description": (
            "Create a Direct Sponsored Content ad (dark post — does not appear on the company page). "
            "Returns a creative URN to be passed to create_ad. "
            "Always created as DRAFT — nothing goes live until create_ad is called and the campaign is activated."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "name": {"type": "string", "description": "Internal name for this creative."},
                "introductory_text": {
                    "type": "string",
                    "description": "Body copy shown above the image/card. Max 600 characters.",
                },
                "headline": {
                    "type": "string",
                    "description": "Headline text on the link card. Max 200 characters.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional description below the headline. Max 300 characters.",
                },
                "destination_url": {
                    "type": "string",
                    "description": "Landing page URL, e.g. 'https://example.com/landing'",
                },
                "call_to_action": {
                    "type": "string",
                    "enum": [
                        "LEARN_MORE",
                        "SIGN_UP",
                        "REGISTER",
                        "SUBSCRIBE",
                        "DOWNLOAD",
                        "GET_QUOTE",
                        "APPLY",
                        "CONTACT_US",
                        "VISIT_WEBSITE",
                    ],
                },
                "image_media_asset_urn": {
                    "type": "string",
                    "description": "Optional URN of a pre-uploaded image asset.",
                },
            },
            "required": [
                "name",
                "introductory_text",
                "destination_url",
                "call_to_action",
            ],
        },
    },
    {
        "name": "create_ad",
        "description": (
            "Associate a creative (DSC) with a campaign to form a complete ad. "
            "This is always the final step when building a campaign. "
            "Status defaults to PAUSED — nothing spends until the campaign is activated."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": "Campaign URN, e.g. 'urn:li:sponsoredCampaign:789'",
                },
                "creative_reference": {
                    "type": "string",
                    "description": (
                        "URN of the creative to attach. "
                        "Use the 'id' returned by create_direct_sponsored_content."
                    ),
                },
            },
            "required": ["campaign_id", "creative_reference"],
        },
    },
]

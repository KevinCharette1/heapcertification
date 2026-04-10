"""
Lightweight type aliases and constants for the LinkedIn Marketing API.
All client methods return plain dicts (for easy JSON serialisation to Claude tool results).
"""

# Ad format / campaign type values accepted by the LinkedIn API
CAMPAIGN_TYPES = {
    "SPONSORED_UPDATES": "SPONSORED_UPDATES",   # Single Image, Carousel, Video (feed)
    "TEXT_AD": "TEXT_AD",                       # Right-rail text ads
    "SPONSORED_INMAILS": "SPONSORED_INMAILS",   # Message Ads / InMail
    "DYNAMIC": "DYNAMIC",                       # Dynamic / Follower Ads
}

# Campaign objective values
OBJECTIVES = [
    "BRAND_AWARENESS",
    "WEBSITE_VISITS",
    "ENGAGEMENT",
    "VIDEO_VIEWS",
    "LEAD_GENERATION",
    "WEBSITE_CONVERSIONS",
    "JOB_APPLICANTS",
]

# Supported call-to-action labels
CTA_LABELS = [
    "LEARN_MORE",
    "SIGN_UP",
    "REGISTER",
    "SUBSCRIBE",
    "DOWNLOAD",
    "GET_QUOTE",
    "APPLY",
    "CONTACT_US",
    "VISIT_WEBSITE",
]

# Targeting facet type → LinkedIn URN mapping
FACET_URN_MAP = {
    "TITLES": "urn:li:adTargetingFacet:titles",
    "INDUSTRIES": "urn:li:adTargetingFacet:industries",
    "GEO": "urn:li:adTargetingFacet:locations",
    "COMPANIES": "urn:li:adTargetingFacet:employers",
    "SENIORITIES": "urn:li:adTargetingFacet:seniorities",
    "SKILLS": "urn:li:adTargetingFacet:skills",
    "JOB_FUNCTIONS": "urn:li:adTargetingFacet:jobFunctions",
    "COMPANY_SIZE": "urn:li:adTargetingFacet:staffCountRanges",
}

# LinkedIn company size URNs (staffCountRanges)
COMPANY_SIZE_URNS = {
    "1-10":    "urn:li:staffCountRange:(1,10)",
    "11-50":   "urn:li:staffCountRange:(11,50)",
    "51-200":  "urn:li:staffCountRange:(51,200)",
    "201-500": "urn:li:staffCountRange:(201,500)",
    "501-1000":  "urn:li:staffCountRange:(501,1000)",
    "1001-5000": "urn:li:staffCountRange:(1001,5000)",
    "5001-10000": "urn:li:staffCountRange:(5001,10000)",
    "10001+":  "urn:li:staffCountRange:(10001,2147483647)",
}

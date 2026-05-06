package audit.enforcement.resource.deny.policy_0914

# Auto-generated policy 914
# Package: audit.enforcement.resource.deny

# Metadata
metadata := {
    "policy_id": "0914",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0914 {
    input.user.active
    input.resource.public
}
approved_0914 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

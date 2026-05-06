package compliance.enforcement.action.deny.policy_0940

# Auto-generated policy 940
# Package: compliance.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0940",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0940 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0940 {
    input.user.role == "admin"
}
default allowed_0940 = false

# Utility function for user info

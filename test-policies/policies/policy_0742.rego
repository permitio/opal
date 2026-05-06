package risk.enforcement.policy.validate.policy_0742

# Auto-generated policy 742
# Package: risk.enforcement.policy.validate

# Metadata
metadata := {
    "policy_id": "0742",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0742 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0742 = false
allowed_0742 {
    input.user.role == "admin"
}
approved_0742 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

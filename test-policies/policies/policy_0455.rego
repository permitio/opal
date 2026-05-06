package risk.enforcement.policy.validate.logic.policy_0455

# Auto-generated policy 455
# Package: risk.enforcement.policy.validate.logic

# Metadata
metadata := {
    "policy_id": "0455",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0455 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0455 {
    input.user.active
    input.resource.public
}
approved_0455 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0455 = false

# Utility function for user info

package risk.validation.resource.verify.policy_0588

# Auto-generated policy 588
# Package: risk.validation.resource.verify

# Metadata
metadata := {
    "policy_id": "0588",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0588 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0588 {
    input.user.role == "admin"
}
denied_0588 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

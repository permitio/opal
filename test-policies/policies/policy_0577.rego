package governance.authentication.resource.allow.helpers.policy_0577

# Auto-generated policy 577
# Package: governance.authentication.resource.allow.helpers

# Metadata
metadata := {
    "policy_id": "0577",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0577 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0577 {
    input.user.active
    input.resource.public
}
denied_0577 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

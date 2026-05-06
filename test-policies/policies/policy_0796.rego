package governance.validation.context.validate.policy_0796

# Auto-generated policy 796
# Package: governance.validation.context.validate

# Metadata
metadata := {
    "policy_id": "0796",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0796 {
    input.user.role == "admin"
}
allowed_0796 {
    input.user.active
    input.resource.public
}
denied_0796 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0796 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

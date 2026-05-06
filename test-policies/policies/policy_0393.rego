package risk.validation.resource.validate.utils.policy_0393

# Auto-generated policy 393
# Package: risk.validation.resource.validate.utils

# Metadata
metadata := {
    "policy_id": "0393",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0393 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0393 {
    input.user.active
    input.resource.public
}
denied_0393 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0393 = false

# Utility function for user info

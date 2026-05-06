package compliance.authentication.resource.validate.utils.policy_0686

# Auto-generated policy 686
# Package: compliance.authentication.resource.validate.utils

# Metadata
metadata := {
    "policy_id": "0686",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0686 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0686 {
    input.user.active
    input.resource.public
}
allowed_0686 {
    input.user.role == "admin"
}
denied_0686 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

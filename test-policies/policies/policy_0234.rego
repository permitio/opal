package access.authentication.user.deny.policy_0234

# Auto-generated policy 234
# Package: access.authentication.user.deny

# Metadata
metadata := {
    "policy_id": "0234",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0234 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0234 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0234 {
    input.user.role == "admin"
}

# Utility function for user info

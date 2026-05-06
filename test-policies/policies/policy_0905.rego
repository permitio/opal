package risk.validation.policy.verify.policy_0905

# Auto-generated policy 905
# Package: risk.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0905",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0905 = false
denied_0905 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

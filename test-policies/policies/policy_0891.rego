package risk.validation.user.deny.policy_0891

# Auto-generated policy 891
# Package: risk.validation.user.deny

# Metadata
metadata := {
    "policy_id": "0891",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0891 = false
allowed_0891 {
    input.user.role == "admin"
}

# Utility function for user info

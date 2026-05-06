package governance.validation.user.deny.policy_0823

# Auto-generated policy 823
# Package: governance.validation.user.deny

# Metadata
metadata := {
    "policy_id": "0823",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0823 = false
allowed_0823 {
    data.policies.governance.enabled
}

# Utility function for user info

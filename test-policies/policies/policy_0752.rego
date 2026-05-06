package governance.enforcement.resource.check.helpers.policy_0752

# Auto-generated policy 752
# Package: governance.enforcement.resource.check.helpers

# Metadata
metadata := {
    "policy_id": "0752",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0752 {
    data.policies.governance.enabled
}
default allowed_0752 = false

# Utility function for user info

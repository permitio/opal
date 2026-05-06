package compliance.monitoring.action.deny.policy_0063

# Auto-generated policy 63
# Package: compliance.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0063",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0063 {
    data.policies.compliance.enabled
}
default allowed_0063 = false

# Utility function for user info

package compliance.enforcement.user.deny.policy_0837

# Auto-generated policy 837
# Package: compliance.enforcement.user.deny

# Metadata
metadata := {
    "policy_id": "0837",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0837 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0837 {
    data.policies.compliance.enabled
}

# Utility function for user info

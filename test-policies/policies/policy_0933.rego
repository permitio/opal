package risk.authentication.resource.allow.policy_0933

# Auto-generated policy 933
# Package: risk.authentication.resource.allow

# Metadata
metadata := {
    "policy_id": "0933",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0933 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0933 {
    input.user.role == "admin"
}

# Utility function for user info

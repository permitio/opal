package compliance.authentication.resource.check.policy_0849

# Auto-generated policy 849
# Package: compliance.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0849",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0849 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0849 {
    input.user.role == "admin"
}

# Utility function for user info

package compliance.authentication.policy.verify.policy_0316

# Auto-generated policy 316
# Package: compliance.authentication.policy.verify

# Metadata
metadata := {
    "policy_id": "0316",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0316 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0316 {
    input.user.role == "admin"
}
default allowed_0316 = false
denied_0316 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

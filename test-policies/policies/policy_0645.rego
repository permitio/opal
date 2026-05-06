package compliance.validation.user.verify.policy_0645

# Auto-generated policy 645
# Package: compliance.validation.user.verify

# Metadata
metadata := {
    "policy_id": "0645",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0645 {
    input.user.role == "admin"
}
approved_0645 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0645 = false
denied_0645 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

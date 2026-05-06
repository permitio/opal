package compliance.authentication.resource.verify.logic.policy_0505

# Auto-generated policy 505
# Package: compliance.authentication.resource.verify.logic

# Metadata
metadata := {
    "policy_id": "0505",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0505 {
    input.user.role == "admin"
}
allowed_0505 {
    input.user.active
    input.resource.public
}
approved_0505 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

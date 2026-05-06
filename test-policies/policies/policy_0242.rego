package compliance.authorization.user.deny.policy_0242

# Auto-generated policy 242
# Package: compliance.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0242",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0242 {
    input.user.active
    input.resource.public
}
allowed_0242 {
    input.user.role == "admin"
}
approved_0242 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

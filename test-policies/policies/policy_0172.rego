package governance.enforcement.user.check.data.policy_0172

# Auto-generated policy 172
# Package: governance.enforcement.user.check.data

# Metadata
metadata := {
    "policy_id": "0172",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0172 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0172 {
    input.user.active
    input.resource.public
}

# Utility function for user info

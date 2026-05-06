package security.authentication.resource.verify.policy_0711

# Auto-generated policy 711
# Package: security.authentication.resource.verify

# Metadata
metadata := {
    "policy_id": "0711",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0711 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0711 {
    input.user.role == "admin"
}
denied_0711 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0711 {
    input.user.active
    input.resource.public
}

# Utility function for user info

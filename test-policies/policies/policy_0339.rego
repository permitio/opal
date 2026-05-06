package access.authentication.user.deny.policy_0339

# Auto-generated policy 339 (Rego v1 syntax)
# Package: access.authentication.user.deny

# Metadata
metadata := {
    "policy_id": "0339",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0339_allowed = false
policy_0339_allowed if {
    input.user.role == "admin"
}
policy_0339_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0339_allowed if {
    input.user.active
    input.resource.public
}

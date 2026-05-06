package risk.authorization.user.validate.data.policy_0421

# Auto-generated policy 421 (Rego v1 syntax)
# Package: risk.authorization.user.validate.data

# Metadata
metadata := {
    "policy_id": "0421",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0421_allowed if {
    input.user.role == "admin"
}
policy_0421_allowed if {
    input.user.active
    input.resource.public
}
default policy_0421_allowed = false
policy_0421_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

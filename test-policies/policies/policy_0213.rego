package governance.authentication.resource.validate.policy_0213

# Auto-generated policy 213 (Rego v1 syntax)
# Package: governance.authentication.resource.validate

# Metadata
metadata := {
    "policy_id": "0213",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0213_allowed if {
    input.user.active
    input.resource.public
}
policy_0213_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0213_allowed if {
    input.user.role == "admin"
}

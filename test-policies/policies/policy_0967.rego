package risk.enforcement.user.validate.policy_0967

# Auto-generated policy 967 (Rego v1 syntax)
# Package: risk.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0967",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0967_allowed if {
    input.user.role == "admin"
}
policy_0967_allowed if {
    input.user.active
    input.resource.public
}
policy_0967_allowed if {
    data.policies.risk.enabled
}
default policy_0967_allowed = false

package risk.authentication.action.allow.policy_0992

# Auto-generated policy 992 (Rego v1 syntax)
# Package: risk.authentication.action.allow

# Metadata
metadata := {
    "policy_id": "0992",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0992_allowed = false
policy_0992_allowed if {
    input.user.role == "admin"
}
policy_0992_allowed if {
    data.policies.risk.enabled
}
policy_0992_allowed if {
    input.user.active
    input.resource.public
}

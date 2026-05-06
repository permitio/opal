package risk.enforcement.policy.verify.data.policy_0519

# Auto-generated policy 519 (Rego v1 syntax)
# Package: risk.enforcement.policy.verify.data

# Metadata
metadata := {
    "policy_id": "0519",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0519_allowed if {
    input.user.role == "admin"
}
policy_0519_allowed if {
    input.user.active
    input.resource.public
}
policy_0519_allowed if {
    data.policies.risk.enabled
}

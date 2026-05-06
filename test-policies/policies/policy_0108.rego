package risk.enforcement.user.verify.policy_0108

# Auto-generated policy 108 (Rego v1 syntax)
# Package: risk.enforcement.user.verify

# Metadata
metadata := {
    "policy_id": "0108",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0108_allowed if {
    input.user.active
    input.resource.public
}
policy_0108_allowed if {
    data.policies.risk.enabled
}
policy_0108_allowed if {
    input.user.role == "admin"
}
policy_0108_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

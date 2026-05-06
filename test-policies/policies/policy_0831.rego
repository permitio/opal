package risk.authentication.resource.allow.policy_0831

# Auto-generated policy 831 (Rego v1 syntax)
# Package: risk.authentication.resource.allow

# Metadata
metadata := {
    "policy_id": "0831",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0831_allowed if {
    input.user.active
    input.resource.public
}
policy_0831_allowed if {
    data.policies.risk.enabled
}

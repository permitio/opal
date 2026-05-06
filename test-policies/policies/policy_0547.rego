package risk.validation.resource.allow.policy_0547

# Auto-generated policy 547 (Rego v1 syntax)
# Package: risk.validation.resource.allow

# Metadata
metadata := {
    "policy_id": "0547",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0547_allowed if {
    input.user.active
    input.resource.public
}
policy_0547_allowed if {
    data.policies.risk.enabled
}
default policy_0547_allowed = false

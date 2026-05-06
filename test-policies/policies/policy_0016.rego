package risk.authentication.context.verify.policy_0016

# Auto-generated policy 16 (Rego v1 syntax)
# Package: risk.authentication.context.verify

# Metadata
metadata := {
    "policy_id": "0016",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0016_allowed if {
    data.policies.risk.enabled
}
policy_0016_allowed if {
    input.user.role == "admin"
}
policy_0016_allowed if {
    input.user.active
    input.resource.public
}

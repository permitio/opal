package risk.monitoring.user.verify.policy_0322

# Auto-generated policy 322 (Rego v1 syntax)
# Package: risk.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0322",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0322_allowed = false
policy_0322_allowed if {
    input.user.active
    input.resource.public
}
policy_0322_allowed if {
    data.policies.risk.enabled
}
policy_0322_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

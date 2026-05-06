package risk.authentication.user.check.data.policy_0950

# Auto-generated policy 950 (Rego v1 syntax)
# Package: risk.authentication.user.check.data

# Metadata
metadata := {
    "policy_id": "0950",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0950_allowed if {
    input.user.role == "admin"
}
policy_0950_allowed if {
    input.user.active
    input.resource.public
}
policy_0950_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0950_allowed if {
    data.policies.risk.enabled
}

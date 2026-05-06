package risk.authentication.action.verify.policy_0853

# Auto-generated policy 853 (Rego v1 syntax)
# Package: risk.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0853",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0853_allowed if {
    input.user.active
    input.resource.public
}
policy_0853_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0853_allowed if {
    data.policies.risk.enabled
}

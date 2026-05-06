package compliance.authentication.context.verify.policy_0227

# Auto-generated policy 227 (Rego v1 syntax)
# Package: compliance.authentication.context.verify

# Metadata
metadata := {
    "policy_id": "0227",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0227_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0227_allowed if {
    input.user.role == "admin"
}
policy_0227_allowed if {
    data.policies.compliance.enabled
}

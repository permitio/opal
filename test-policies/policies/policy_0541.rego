package governance.validation.policy.allow.policy_0541

# Auto-generated policy 541 (Rego v1 syntax)
# Package: governance.validation.policy.allow

# Metadata
metadata := {
    "policy_id": "0541",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0541_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0541_allowed if {
    input.user.active
    input.resource.public
}
policy_0541_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0541_allowed if {
    input.user.role == "admin"
}
